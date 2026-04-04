"""
Tests for F-B.3 (override endpoint models) and F-B.4 (governed state persistence).

Verifies:
  - OverrideRequest/OverrideResponse model validation
  - save/load governed state round-trip (sync and async)
  - get_or_create returns fresh state on miss, existing state on hit
  - Invariant: overrides write to ObservedState, not directly to Normalized/Governance
"""
from __future__ import annotations

import json
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.api.models import (
    OverrideGovernanceResult,
    OverrideItem,
    OverrideRequest,
    OverrideResponse,
)
from app.agent.state.models import (
    DispatchContractState,
    ExportProfileState,
    GovernedSessionState,
    ManufacturerMappingState,
    ObservedExtraction,
    ObservedState,
    SealaiNormIdentity,
    SealaiNormState,
    UserOverride,
)
from app.agent.state.persistence import (
    _governed_state_key,
    get_or_create_governed_state_async,
    load_governed_state,
    load_governed_state_async,
    save_governed_state,
    save_governed_state_async,
)
from app.agent.state.reducers import (
    reduce_asserted_to_governance,
    reduce_normalized_to_asserted,
    reduce_observed_to_normalized,
)


# ---------------------------------------------------------------------------
# Fake Redis (in-memory dict)
# ---------------------------------------------------------------------------

class FakeRedis:
    """Minimal in-memory Redis stub for sync tests."""

    def __init__(self):
        self._store: dict[str, str] = {}

    def set(self, key: str, value: str, *, ex: Optional[int] = None) -> None:
        self._store[key] = value

    def get(self, key: str) -> Optional[str]:
        return self._store.get(key)


class FakeRedisAsync:
    """Minimal in-memory Redis stub for async tests."""

    def __init__(self):
        self._store: dict[str, str] = {}

    async def set(self, key: str, value: str, *, ex: Optional[int] = None) -> None:
        self._store[key] = value

    async def get(self, key: str) -> Optional[str]:
        return self._store.get(key)


# ---------------------------------------------------------------------------
# F-B.3 — API model tests
# ---------------------------------------------------------------------------

class TestOverrideItemModel:

    def test_basic_valid(self):
        item = OverrideItem(field_name="medium", value="Dampf")
        assert item.field_name == "medium"
        assert item.value == "Dampf"
        assert item.unit is None

    def test_with_unit(self):
        item = OverrideItem(field_name="pressure_bar", value=6.0, unit="bar")
        assert item.unit == "bar"

    def test_rejects_empty_field_name(self):
        with pytest.raises(Exception):
            OverrideItem(field_name="", value="Wasser")

    def test_rejects_extra_fields(self):
        with pytest.raises(Exception):
            OverrideItem(field_name="medium", value="Dampf", unexpected="x")


class TestOverrideRequestModel:

    def test_valid_single_override(self):
        req = OverrideRequest(
            overrides=[OverrideItem(field_name="medium", value="Öl")],
            turn_index=1,
        )
        assert len(req.overrides) == 1
        assert req.turn_index == 1

    def test_rejects_empty_overrides_list(self):
        with pytest.raises(Exception):
            OverrideRequest(overrides=[], turn_index=0)

    def test_turn_index_defaults_to_zero(self):
        req = OverrideRequest(overrides=[OverrideItem(field_name="medium", value="Öl")])
        assert req.turn_index == 0

    def test_rejects_negative_turn_index(self):
        with pytest.raises(Exception):
            OverrideRequest(
                overrides=[OverrideItem(field_name="medium", value="Öl")],
                turn_index=-1,
            )


class TestOverrideResponseModel:

    def test_round_trip(self):
        gov = OverrideGovernanceResult(
            gov_class="B",
            rfq_admissible=False,
            blocking_unknowns=["pressure_bar"],
        )
        resp = OverrideResponse(
            session_id="sess-1",
            applied_fields=["medium"],
            governance=gov,
        )
        assert resp.session_id == "sess-1"
        assert resp.applied_fields == ["medium"]
        assert resp.governance.gov_class == "B"
        assert resp.governance.blocking_unknowns == ["pressure_bar"]

    def test_governance_defaults(self):
        gov = OverrideGovernanceResult()
        assert gov.gov_class is None
        assert gov.rfq_admissible is False
        assert gov.blocking_unknowns == []


# ---------------------------------------------------------------------------
# F-B.4 — Persistence sync tests
# ---------------------------------------------------------------------------

class TestGovernedStatePersistenceSync:

    def test_key_format(self):
        key = _governed_state_key("tenant-A", "session-1")
        assert key == "governed_state:tenant-A:session-1"

    def test_save_and_load_round_trip(self):
        redis = FakeRedis()
        state = GovernedSessionState()
        save_governed_state(state, tenant_id="t1", session_id="s1", redis_client=redis)

        loaded = load_governed_state(tenant_id="t1", session_id="s1", redis_client=redis)
        assert loaded is not None
        assert isinstance(loaded, GovernedSessionState)

    def test_load_missing_key_returns_none(self):
        redis = FakeRedis()
        loaded = load_governed_state(tenant_id="t1", session_id="missing", redis_client=redis)
        assert loaded is None

    def test_state_with_overrides_survives_round_trip(self):
        redis = FakeRedis()
        observed = ObservedState().with_override(
            UserOverride(field_name="medium", override_value="Dampf", turn_index=1)
        )
        state = GovernedSessionState(observed=observed)
        save_governed_state(state, tenant_id="t1", session_id="s1", redis_client=redis)

        loaded = load_governed_state(tenant_id="t1", session_id="s1", redis_client=redis)
        assert loaded is not None
        assert len(loaded.observed.user_overrides) == 1
        assert loaded.observed.user_overrides[0].field_name == "medium"

    def test_norm_object_survives_round_trip(self):
        redis = FakeRedis()
        state = GovernedSessionState(
            sealai_norm=SealaiNormState(
                status="governed",
                identity=SealaiNormIdentity(
                    sealai_request_id="sealai-sync-roundtrip",
                    norm_version="sealai_norm_v1",
                    requirement_class_id="PTFE10",
                ),
            )
        )
        save_governed_state(state, tenant_id="t1", session_id="norm-sync", redis_client=redis)

        loaded = load_governed_state(tenant_id="t1", session_id="norm-sync", redis_client=redis)
        assert loaded is not None
        assert loaded.sealai_norm.identity.norm_version == "sealai_norm_v1"
        assert loaded.sealai_norm.identity.requirement_class_id == "PTFE10"

    def test_export_profile_survives_round_trip(self):
        redis = FakeRedis()
        state = GovernedSessionState(
            export_profile=ExportProfileState(
                status="ready",
                export_profile_version="sealai_export_profile_v1",
                sealai_request_id="sealai-sync-export",
                requirement_class_id="PTFE10",
            )
        )
        save_governed_state(state, tenant_id="t1", session_id="export-sync", redis_client=redis)

        loaded = load_governed_state(tenant_id="t1", session_id="export-sync", redis_client=redis)
        assert loaded is not None
        assert loaded.export_profile.export_profile_version == "sealai_export_profile_v1"
        assert loaded.export_profile.requirement_class_id == "PTFE10"

    def test_manufacturer_mapping_survives_round_trip(self):
        redis = FakeRedis()
        state = GovernedSessionState(
            manufacturer_mapping=ManufacturerMappingState(
                status="mapped",
                mapping_version="manufacturer_mapping_v1",
                selected_manufacturer="Acme",
                mapped_material_family="PTFE",
            )
        )
        save_governed_state(state, tenant_id="t1", session_id="mapping-sync", redis_client=redis)

        loaded = load_governed_state(tenant_id="t1", session_id="mapping-sync", redis_client=redis)
        assert loaded is not None
        assert loaded.manufacturer_mapping.mapping_version == "manufacturer_mapping_v1"
        assert loaded.manufacturer_mapping.selected_manufacturer == "Acme"

    def test_dispatch_contract_survives_round_trip(self):
        redis = FakeRedis()
        state = GovernedSessionState(
            dispatch_contract=DispatchContractState(
                status="ready",
                contract_version="dispatch_contract_v1",
                sealai_request_id="sealai-sync-contract",
                selected_manufacturer="Acme",
            )
        )
        save_governed_state(state, tenant_id="t1", session_id="contract-sync", redis_client=redis)

        loaded = load_governed_state(tenant_id="t1", session_id="contract-sync", redis_client=redis)
        assert loaded is not None
        assert loaded.dispatch_contract.contract_version == "dispatch_contract_v1"
        assert loaded.dispatch_contract.sealai_request_id == "sealai-sync-contract"

    def test_load_corrupted_data_returns_none(self):
        redis = FakeRedis()
        key = _governed_state_key("t1", "s1")
        redis.set(key, "not-json-at-all{{{")

        loaded = load_governed_state(tenant_id="t1", session_id="s1", redis_client=redis)
        assert loaded is None

    def test_overwrite_existing_state(self):
        redis = FakeRedis()
        state1 = GovernedSessionState(analysis_cycle=0)
        state2 = GovernedSessionState(analysis_cycle=2)
        save_governed_state(state1, tenant_id="t1", session_id="s1", redis_client=redis)
        save_governed_state(state2, tenant_id="t1", session_id="s1", redis_client=redis)

        loaded = load_governed_state(tenant_id="t1", session_id="s1", redis_client=redis)
        assert loaded is not None
        assert loaded.analysis_cycle == 2

    def test_different_sessions_are_isolated(self):
        redis = FakeRedis()
        s1 = GovernedSessionState(analysis_cycle=1)
        s2 = GovernedSessionState(analysis_cycle=5)
        save_governed_state(s1, tenant_id="t1", session_id="sessionA", redis_client=redis)
        save_governed_state(s2, tenant_id="t1", session_id="sessionB", redis_client=redis)

        loaded_a = load_governed_state(tenant_id="t1", session_id="sessionA", redis_client=redis)
        loaded_b = load_governed_state(tenant_id="t1", session_id="sessionB", redis_client=redis)
        assert loaded_a.analysis_cycle == 1
        assert loaded_b.analysis_cycle == 5

    def test_different_tenants_are_isolated(self):
        redis = FakeRedis()
        s_t1 = GovernedSessionState(analysis_cycle=1)
        s_t2 = GovernedSessionState(analysis_cycle=9)
        save_governed_state(s_t1, tenant_id="tenant1", session_id="s1", redis_client=redis)
        save_governed_state(s_t2, tenant_id="tenant2", session_id="s1", redis_client=redis)

        loaded_t1 = load_governed_state(tenant_id="tenant1", session_id="s1", redis_client=redis)
        loaded_t2 = load_governed_state(tenant_id="tenant2", session_id="s1", redis_client=redis)
        assert loaded_t1.analysis_cycle == 1
        assert loaded_t2.analysis_cycle == 9


# ---------------------------------------------------------------------------
# F-B.4 — Persistence async tests
# ---------------------------------------------------------------------------

class TestGovernedStatePersistenceAsync:

    @pytest.mark.asyncio
    async def test_async_save_and_load_round_trip(self):
        redis = FakeRedisAsync()
        state = GovernedSessionState()
        await save_governed_state_async(state, tenant_id="t1", session_id="s1", redis_client=redis)

        loaded = await load_governed_state_async(tenant_id="t1", session_id="s1", redis_client=redis)
        assert loaded is not None
        assert isinstance(loaded, GovernedSessionState)

    @pytest.mark.asyncio
    async def test_async_load_missing_returns_none(self):
        redis = FakeRedisAsync()
        loaded = await load_governed_state_async(
            tenant_id="t1", session_id="nonexistent", redis_client=redis
        )
        assert loaded is None

    @pytest.mark.asyncio
    async def test_async_norm_object_survives_round_trip(self):
        redis = FakeRedisAsync()
        state = GovernedSessionState(
            sealai_norm=SealaiNormState(
                status="rfq_ready",
                identity=SealaiNormIdentity(
                    sealai_request_id="sealai-async-roundtrip",
                    norm_version="sealai_norm_v1",
                    requirement_class_id="PTFE10",
                ),
            )
        )
        await save_governed_state_async(
            state, tenant_id="t1", session_id="norm-async", redis_client=redis
        )

        loaded = await load_governed_state_async(
            tenant_id="t1", session_id="norm-async", redis_client=redis
        )
        assert loaded is not None
        assert loaded.sealai_norm.identity.sealai_request_id == "sealai-async-roundtrip"
        assert loaded.sealai_norm.identity.norm_version == "sealai_norm_v1"

    @pytest.mark.asyncio
    async def test_async_export_profile_survives_round_trip(self):
        redis = FakeRedisAsync()
        state = GovernedSessionState(
            export_profile=ExportProfileState(
                status="partial",
                export_profile_version="sealai_export_profile_v1",
                sealai_request_id="sealai-async-export",
                requirement_class_id="PTFE10",
            )
        )
        await save_governed_state_async(
            state, tenant_id="t1", session_id="export-async", redis_client=redis
        )

        loaded = await load_governed_state_async(
            tenant_id="t1", session_id="export-async", redis_client=redis
        )
        assert loaded is not None
        assert loaded.export_profile.sealai_request_id == "sealai-async-export"
        assert loaded.export_profile.export_profile_version == "sealai_export_profile_v1"

    @pytest.mark.asyncio
    async def test_async_manufacturer_mapping_survives_round_trip(self):
        redis = FakeRedisAsync()
        state = GovernedSessionState(
            manufacturer_mapping=ManufacturerMappingState(
                status="partial",
                mapping_version="manufacturer_mapping_v1",
                selected_manufacturer="Acme",
                mapped_material_family="PTFE",
            )
        )
        await save_governed_state_async(
            state, tenant_id="t1", session_id="mapping-async", redis_client=redis
        )

        loaded = await load_governed_state_async(
            tenant_id="t1", session_id="mapping-async", redis_client=redis
        )
        assert loaded is not None
        assert loaded.manufacturer_mapping.mapping_version == "manufacturer_mapping_v1"
        assert loaded.manufacturer_mapping.selected_manufacturer == "Acme"

    @pytest.mark.asyncio
    async def test_async_dispatch_contract_survives_round_trip(self):
        redis = FakeRedisAsync()
        state = GovernedSessionState(
            dispatch_contract=DispatchContractState(
                status="partial",
                contract_version="dispatch_contract_v1",
                sealai_request_id="sealai-async-contract",
                selected_manufacturer="Acme",
            )
        )
        await save_governed_state_async(
            state, tenant_id="t1", session_id="contract-async", redis_client=redis
        )

        loaded = await load_governed_state_async(
            tenant_id="t1", session_id="contract-async", redis_client=redis
        )
        assert loaded is not None
        assert loaded.dispatch_contract.contract_version == "dispatch_contract_v1"
        assert loaded.dispatch_contract.sealai_request_id == "sealai-async-contract"

    @pytest.mark.asyncio
    async def test_get_or_create_creates_fresh_on_miss(self):
        redis = FakeRedisAsync()
        state = await get_or_create_governed_state_async(
            tenant_id="t1", session_id="new-sess", redis_client=redis
        )
        assert isinstance(state, GovernedSessionState)
        assert state.analysis_cycle == 0
        assert state.observed.raw_extractions == []

    @pytest.mark.asyncio
    async def test_get_or_create_returns_existing(self):
        redis = FakeRedisAsync()
        existing = GovernedSessionState(analysis_cycle=3)
        await save_governed_state_async(
            existing, tenant_id="t1", session_id="existing-sess", redis_client=redis
        )

        loaded = await get_or_create_governed_state_async(
            tenant_id="t1", session_id="existing-sess", redis_client=redis
        )
        assert loaded.analysis_cycle == 3

    @pytest.mark.asyncio
    async def test_async_load_corrupted_returns_none(self):
        redis = FakeRedisAsync()
        key = _governed_state_key("t1", "s1")
        await redis.set(key, "corrupted!{[}")

        loaded = await load_governed_state_async(
            tenant_id="t1", session_id="s1", redis_client=redis
        )
        assert loaded is None


# ---------------------------------------------------------------------------
# Override invariant: writes go to ObservedState, not Normalized/Governance
# ---------------------------------------------------------------------------

class TestOverrideInvariant:
    """Verify that override values enter via ObservedState and flow through reducers."""

    def _apply_overrides(self, overrides: list[UserOverride]) -> GovernedSessionState:
        """Simulate what the override endpoint does — no Redis needed."""
        state = GovernedSessionState()
        observed = state.observed
        for ov in overrides:
            observed = observed.with_override(ov)
        normalized = reduce_observed_to_normalized(observed)
        asserted = reduce_normalized_to_asserted(normalized)
        governance = reduce_asserted_to_governance(asserted)
        return state.model_copy(update={
            "observed": observed,
            "normalized": normalized,
            "asserted": asserted,
            "governance": governance,
        })

    def test_override_enters_observed_state(self):
        ov = UserOverride(field_name="medium", override_value="Öl", turn_index=1)
        result = self._apply_overrides([ov])
        assert len(result.observed.user_overrides) == 1
        assert result.observed.user_overrides[0].field_name == "medium"

    def test_override_propagates_to_normalized(self):
        ov = UserOverride(field_name="medium", override_value="Dampf", turn_index=1)
        result = self._apply_overrides([ov])
        assert "medium" in result.normalized.parameters
        assert result.normalized.parameters["medium"].value == "Dampf"
        assert result.normalized.parameters["medium"].source == "user_override"

    def test_override_propagates_to_governance(self):
        overrides = [
            UserOverride(field_name="medium", override_value="Wasser", turn_index=1),
            UserOverride(field_name="pressure_bar", override_value=6.0, turn_index=1),
            UserOverride(field_name="temperature_c", override_value=80.0, turn_index=1),
        ]
        result = self._apply_overrides(overrides)
        # All three core fields overridden → should reach Class A
        assert result.governance.gov_class == "A"
        assert result.governance.rfq_admissible is True

    def test_override_wins_over_existing_llm_extraction(self):
        """Override must beat a pre-existing LLM extraction for same field."""
        state = GovernedSessionState()
        # Seed with an LLM extraction
        observed = state.observed.with_extraction(
            ObservedExtraction(
                field_name="medium", raw_value="Wasser", confidence=1.0, turn_index=0
            )
        )
        # Now apply override with different value
        observed = observed.with_override(
            UserOverride(field_name="medium", override_value="Dampf", turn_index=1)
        )
        normalized = reduce_observed_to_normalized(observed)
        # Override wins
        assert normalized.parameters["medium"].value == "Dampf"
        assert normalized.parameters["medium"].source == "user_override"
