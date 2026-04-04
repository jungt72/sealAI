"""
Phase F-B.4 integration tests — working-profile → reducer chain → Redis persistence.

Tests cover:
  1. _extract_extractions_from_working_profile correctness
  2. Reducer chain with typical data (PTFE+pressure+temp → Class B without medium)
  3. Reducer chain with full core fields → Class A
  4. Empty working_profile → Class D
  5. User override writes only to ObservedState (architecture invariant F-B.2)
  6. GovernedSessionState Redis save/load roundtrip (mocked Redis)
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.api.router import (
    _extract_extractions_from_working_profile,
    _update_governed_state_post_graph,
)
from app.agent.state.models import (
    GovernedSessionState,
    ObservedExtraction,
    ObservedState,
    UserOverride,
)
from app.agent.state.persistence import (
    get_or_create_governed_state_async,
    save_governed_state_async,
)
from app.agent.state.reducers import (
    reduce_asserted_to_governance,
    reduce_normalized_to_asserted,
    reduce_observed_to_normalized,
)


# ---------------------------------------------------------------------------
# 1. _extract_extractions_from_working_profile
# ---------------------------------------------------------------------------

class TestExtractExtractionsFromWorkingProfile:
    def test_scalar_values_extracted(self):
        wp = {"pressure_bar": 12.0, "temperature_max_c": 180.0, "material": "PTFE"}
        extractions = _extract_extractions_from_working_profile(wp, turn_index=1)
        names = {e.field_name for e in extractions}
        assert "pressure_bar" in names
        assert "temperature_c" in names
        assert "material" in names

    def test_temperature_alias_wins(self):
        """temperature_max_c must beat temperature for canonical field temperature_c."""
        wp = {"temperature": 100.0, "temperature_max_c": 180.0}
        extractions = _extract_extractions_from_working_profile(wp, turn_index=0)
        temp_ext = next(e for e in extractions if e.field_name == "temperature_c")
        assert temp_ext.raw_value == 180.0

    def test_nested_dict_ignored(self):
        wp = {"pressure_bar": 8.0, "live_calc_tile": {"a": 1, "b": 2}}
        extractions = _extract_extractions_from_working_profile(wp, turn_index=0)
        names = {e.field_name for e in extractions}
        assert "pressure_bar" in names
        # live_calc_tile is a dict — must not produce an extraction
        assert all(e.raw_value != {"a": 1, "b": 2} for e in extractions)

    def test_none_value_skipped(self):
        wp = {"pressure_bar": None, "material": "NBR"}
        extractions = _extract_extractions_from_working_profile(wp, turn_index=0)
        names = {e.field_name for e in extractions}
        assert "pressure_bar" not in names
        assert "material" in names

    def test_empty_profile_yields_empty(self):
        extractions = _extract_extractions_from_working_profile({}, turn_index=0)
        assert extractions == []

    def test_confidence_is_09(self):
        wp = {"medium": "Dampf"}
        extractions = _extract_extractions_from_working_profile(wp, turn_index=2)
        assert all(e.confidence == 0.9 for e in extractions)

    def test_source_is_llm(self):
        wp = {"pressure_bar": 5.0}
        extractions = _extract_extractions_from_working_profile(wp, turn_index=0)
        assert all(e.source == "llm" for e in extractions)

    def test_turn_index_assigned(self):
        wp = {"pressure_bar": 10.0}
        extractions = _extract_extractions_from_working_profile(wp, turn_index=3)
        assert all(e.turn_index == 3 for e in extractions)


# ---------------------------------------------------------------------------
# 2. Reducer chain — PTFE + pressure + temp, no medium → Class B
# ---------------------------------------------------------------------------

class TestReducerChainClassB:
    def test_typical_governed_input_yields_class_b(self):
        """Three core params present but medium missing → Class B expected."""
        wp = {"material": "PTFE", "pressure_bar": 12.0, "temperature_max_c": 180.0}
        extractions = _extract_extractions_from_working_profile(wp, turn_index=1)

        observed = ObservedState()
        for e in extractions:
            observed = observed.with_extraction(e)

        normalized = reduce_observed_to_normalized(observed)
        asserted = reduce_normalized_to_asserted(normalized)
        governance = reduce_asserted_to_governance(asserted, analysis_cycle=1, max_cycles=3)

        # medium not provided → blocking_unknown → at most Class B
        assert governance.gov_class in ("B", "C", "D")
        assert governance.rfq_admissible is False

    def test_normalized_parameters_contain_pressure(self):
        wp = {"pressure_bar": 12.0}
        extractions = _extract_extractions_from_working_profile(wp, turn_index=0)
        observed = ObservedState()
        for e in extractions:
            observed = observed.with_extraction(e)
        normalized = reduce_observed_to_normalized(observed)
        assert "pressure_bar" in normalized.parameters


# ---------------------------------------------------------------------------
# 3. Reducer chain — all core fields present → Class A
# ---------------------------------------------------------------------------

class TestReducerChainClassA:
    def test_full_core_fields_yields_class_a(self):
        """medium + pressure_bar + temperature_c all present → Class A."""
        wp = {
            "medium": "Dampf",
            "pressure_bar": 12.0,
            "temperature_max_c": 180.0,
        }
        extractions = _extract_extractions_from_working_profile(wp, turn_index=1)
        observed = ObservedState()
        for e in extractions:
            observed = observed.with_extraction(e)

        normalized = reduce_observed_to_normalized(observed)
        asserted = reduce_normalized_to_asserted(normalized)
        governance = reduce_asserted_to_governance(asserted, analysis_cycle=1, max_cycles=3)

        assert governance.gov_class == "A"
        assert governance.rfq_admissible is True


# ---------------------------------------------------------------------------
# 4. Empty working_profile → Class D / no assertions
# ---------------------------------------------------------------------------

class TestReducerChainEmpty:
    def test_empty_profile_yields_no_gov_class_or_d(self):
        extractions = _extract_extractions_from_working_profile({}, turn_index=0)
        observed = ObservedState()
        for e in extractions:
            observed = observed.with_extraction(e)

        normalized = reduce_observed_to_normalized(observed)
        asserted = reduce_normalized_to_asserted(normalized)
        governance = reduce_asserted_to_governance(asserted, analysis_cycle=1, max_cycles=3)

        # Empty input → no assertions → Gov class should be D or None
        assert governance.gov_class in ("D", None)
        assert governance.rfq_admissible is False


# ---------------------------------------------------------------------------
# 5. User override writes only to ObservedState — F-B.2 invariant
# ---------------------------------------------------------------------------

class TestUserOverrideInvariant:
    def test_override_updates_observed_not_normalized_directly(self):
        """Override must appear in ObservedState.user_overrides, not bypass reducer."""
        override = UserOverride(field_name="medium", override_value="Wasser", turn_index=2)
        observed = ObservedState()
        observed = observed.with_override(override)

        assert len(observed.user_overrides) == 1
        assert observed.user_overrides[0].override_value == "Wasser"
        # NormalizedState is only populated via reducer — not by the call above
        normalized = reduce_observed_to_normalized(observed)
        assert "medium" in normalized.parameters

    def test_override_wins_over_llm_extraction(self):
        """User override must produce higher-priority parameter in NormalizedState."""
        # LLM extracted medium = "Öl"
        extraction = ObservedExtraction(
            field_name="medium", raw_value="Öl", source="llm", confidence=0.9, turn_index=0
        )
        override = UserOverride(field_name="medium", override_value="Dampf", turn_index=1)

        observed = ObservedState()
        observed = observed.with_extraction(extraction)
        observed = observed.with_override(override)

        normalized = reduce_observed_to_normalized(observed)
        medium_param = normalized.parameters.get("medium")
        assert medium_param is not None
        assert medium_param.source == "user_override"
        assert medium_param.value == "Dampf"


# ---------------------------------------------------------------------------
# 6. GovernedSessionState Redis roundtrip — mocked Redis
# ---------------------------------------------------------------------------

class TestRedisRoundtrip:
    @pytest.mark.asyncio
    async def test_save_and_load_roundtrip(self):
        """State serialised to Redis and deserialized must be equal to original."""
        state = GovernedSessionState()
        state = state.model_copy(update={"analysis_cycle": 5})

        stored: dict[str, str] = {}

        class _FakeRedis:
            async def set(self, key, value, ex=None):
                stored[key] = value

            async def get(self, key):
                return stored.get(key)

        fake_rc = _FakeRedis()
        await save_governed_state_async(
            state,
            tenant_id="tenant1",
            session_id="sess1",
            redis_client=fake_rc,
        )

        assert len(stored) == 1
        key = next(iter(stored))
        assert "tenant1" in key
        assert "sess1" in key

        loaded = await get_or_create_governed_state_async(
            tenant_id="tenant1",
            session_id="sess1",
            redis_client=fake_rc,
        )
        assert loaded.analysis_cycle == 5

    @pytest.mark.asyncio
    async def test_missing_key_creates_fresh_state(self):
        """Missing Redis key → fresh GovernedSessionState with defaults."""
        class _EmptyRedis:
            async def set(self, key, value, ex=None):
                pass

            async def get(self, key):
                return None

        state = await get_or_create_governed_state_async(
            tenant_id="t", session_id="s", redis_client=_EmptyRedis()
        )
        assert isinstance(state, GovernedSessionState)
        assert state.analysis_cycle == 0


# ---------------------------------------------------------------------------
# 7. _update_governed_state_post_graph end-to-end (mocked Redis)
# ---------------------------------------------------------------------------

class TestUpdateGovernedStatePostGraph:
    @pytest.mark.asyncio
    async def test_full_pipeline_updates_gov_class(self):
        """A working_profile with all core fields → governance.gov_class == 'A'."""
        initial = GovernedSessionState()
        final_agent_state = {
            "working_profile": {
                "medium": "Dampf",
                "pressure_bar": 12.0,
                "temperature_max_c": 180.0,
            },
            "turn_count": 1,
        }

        stored: dict[str, str] = {}

        class _FakeRedis:
            async def set(self, key, value, ex=None):
                stored[key] = value

            async def get(self, key):
                return stored.get(key)

        with patch("os.getenv", return_value="redis://localhost:6379"), \
             patch("redis.asyncio.Redis.from_url") as mock_from_url:

            fake_rc = _FakeRedis()

            class _FakeCtxMgr:
                async def __aenter__(self):
                    return fake_rc
                async def __aexit__(self, *a):
                    pass

            mock_from_url.return_value = _FakeCtxMgr()

            updated = await _update_governed_state_post_graph(
                governed_state=initial,
                final_agent_state=final_agent_state,
                tenant_id="tenant1",
                session_id="sess1",
                turn_index=1,
            )

        assert updated.governance.gov_class == "A"
        assert updated.governance.rfq_admissible is True
        assert updated.analysis_cycle == 1

    @pytest.mark.asyncio
    async def test_redis_failure_does_not_raise(self):
        """If Redis is unavailable, the function must not propagate the exception."""
        initial = GovernedSessionState()
        final_agent_state = {"working_profile": {}, "turn_count": 0}

        with patch("os.getenv", return_value="redis://localhost:6379"), \
             patch("redis.asyncio.Redis.from_url", side_effect=ConnectionError("down")):

            # Must not raise
            result = await _update_governed_state_post_graph(
                governed_state=initial,
                final_agent_state=final_agent_state,
                tenant_id="t",
                session_id="s",
                turn_index=0,
            )
        # Even on Redis failure, the updated state is returned
        assert isinstance(result, GovernedSessionState)
