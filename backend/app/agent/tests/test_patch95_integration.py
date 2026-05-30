"""Patch 9.5 — end-to-end wiring tests through the REAL pipeline.

One E2E test per wire, exercising the actual route/dispatch functions (not the
isolated builders):
  1. action_chip → override endpoint → State Gate, action_chip_answer provenance
  2. photo + "sifft" → real dispatch → mobile_leakage_triage (no vision/RAG/graph)
  3. sealai:sheet-event → override endpoint → apply_sheet_event (idempotency/stale)
  4. RWDR brief → readiness + one-pager via the real /rwdr/brief endpoint
"""

from __future__ import annotations

import pytest

from app.agent.api.models import ChatRequest, OverrideItem, OverrideRequest
from app.agent.api.router import _resolve_runtime_dispatch, session_override_endpoint
from app.agent.state.persistence import load_governed_state_async
from app.services.auth.dependencies import RequestUser


class _FakeRedisClient:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def __aenter__(self) -> "_FakeRedisClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def set(self, key: str, value: str, *, ex: int | None = None) -> None:
        self._store[key] = value

    async def get(self, key: str) -> str | None:
        return self._store.get(key)


class _FakeRedisFactory:
    def __init__(self, client: _FakeRedisClient) -> None:
        self._client = client

    def from_url(self, *_args, **_kwargs) -> _FakeRedisClient:
        return self._client


async def _skip_snapshot_persistence(*_args, **_kwargs):
    return None


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1", username="tester", sub="user-1", roles=[], scopes=[], tenant_id="tenant-1"
    )


@pytest.fixture
def _override_env(monkeypatch: pytest.MonkeyPatch) -> _FakeRedisClient:
    fake_redis = _FakeRedisClient()
    monkeypatch.setenv("REDIS_URL", "redis://fake")
    import redis.asyncio as redis_asyncio

    monkeypatch.setattr(redis_asyncio, "Redis", _FakeRedisFactory(fake_redis))
    import app.agent.api.loaders as loaders_module

    monkeypatch.setattr(loaders_module, "save_governed_state_snapshot_async", _skip_snapshot_persistence)
    return fake_redis


# --- Wire 1: action_chip → override → State Gate (action_chip_answer) --------


@pytest.mark.asyncio
async def test_wire1_action_chip_provenance_end_to_end(_override_env: _FakeRedisClient) -> None:
    await session_override_endpoint(
        session_id="case-chip",
        request=OverrideRequest(
            overrides=[OverrideItem(field_name="medium", value="Öl")],
            origin="action_chip_answer",
        ),
        current_user=_user(),
    )
    persisted = await load_governed_state_async(
        tenant_id="tenant-1", session_id="case-chip", redis_client=_override_env
    )
    assert persisted is not None
    assert persisted.normalized.parameters["medium"].provenance == "action_chip_answer"


# --- Wire 2: photo + "sifft" → real dispatch → mobile leakage triage ---------


@pytest.mark.asyncio
async def test_wire2_photo_sifft_routes_to_mobile_triage() -> None:
    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="sifft", session_id="case-triage", has_attachment=True),
        current_user=_user(),
    )
    assert dispatch.gate_reason == "mobile_leakage_triage"
    assert dispatch.fast_response is not None
    assert "Leckagefall" in dispatch.fast_response.content
    # Immediate output without vision/RAG/graph (no-empty-spinner).
    trace = dispatch.fast_response.mobile_triage_envelope["trace"]
    assert trace["rag_used"] is False
    assert trace["graph_used"] is False
    assert trace["llm_used"] is False


@pytest.mark.asyncio
async def test_wire2_text_only_sifft_does_not_trigger_triage() -> None:
    # Without an attachment the existing governed path is unchanged.
    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="die dichtung sifft", session_id="case-text", has_attachment=False),
        current_user=_user(),
    )
    assert dispatch.gate_reason != "mobile_leakage_triage"


# --- Wire 3: sheet-event → override → apply_sheet_event (idempotency/stale) --


@pytest.mark.asyncio
async def test_wire3_sheet_event_idempotent_via_override(_override_env: _FakeRedisClient) -> None:
    req = OverrideRequest(
        overrides=[OverrideItem(field_name="temperature_c", value=90, unit="°C")],
        client_event_id="sheet-evt-1",
        turn_index=1,
    )
    first = await session_override_endpoint(session_id="case-sheet", request=req, current_user=_user())
    assert first.applied_fields == ["temperature_c"]

    second = await session_override_endpoint(session_id="case-sheet", request=req, current_user=_user())
    # Same client_event_id → no second mutation.
    assert second.applied_fields == []

    persisted = await load_governed_state_async(
        tenant_id="tenant-1", session_id="case-sheet", redis_client=_override_env
    )
    assert persisted.normalized.parameters["temperature_c"].value == 90
    assert "sheet-evt-1" in persisted.applied_sheet_event_ids


@pytest.mark.asyncio
async def test_wire3_stale_sheet_event_degrades_to_warning(
    _override_env: _FakeRedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Seed a persisted state that already carries a revision (user_turn_index
    # round-trips), so a sheet event against an older revision is stale.
    from app.agent.api import loaders as loaders_module
    from app.agent.state.models import GovernedSessionState
    from app.agent.state.persistence import save_governed_state_async

    await save_governed_state_async(
        tenant_id="tenant-1",
        session_id="case-stale",
        state=GovernedSessionState(user_turn_index=5),
        redis_client=_override_env,
    )

    await session_override_endpoint(
        session_id="case-stale",
        request=OverrideRequest(
            overrides=[OverrideItem(field_name="temperature_c", value=120, unit="°C")],
            client_event_id="stale-evt",
            case_revision_seen=0,  # older than the seeded revision (5)
        ),
        current_user=_user(),
    )
    persisted = await load_governed_state_async(
        tenant_id="tenant-1", session_id="case-stale", redis_client=_override_env
    )
    # Field still applied (case usable, not blocked) + a warning conflict recorded.
    assert persisted.normalized.parameters["temperature_c"].value == 120
    warnings = [c for c in persisted.normalized.conflicts if c.severity == "warning"]
    assert any(c.field_name == "temperature_c" for c in warnings)


# --- Wire 4: RWDR brief → readiness + one-pager via the real endpoint --------


@pytest.mark.asyncio
async def test_wire4_rfq_one_pager_via_brief_endpoint() -> None:
    from app.api.v1.endpoints.rfq import RwdrBriefRequest, generate_rwdr_brief

    result = await generate_rwdr_brief(
        body=RwdrBriefRequest(raw_inquiry="RWDR 45x62x8, Getriebe, Öl, undicht", fields=[]),
        user=_user(),
    )
    # Existing brief keys preserved + V1.6 readiness/one-pager attached.
    assert "status" in result
    assert "rfq_readiness" in result
    assert result["rfq_readiness"]["status"] in {
        "DRAFT",
        "MINIMAL_RFQ",
        "RFQ_WITH_OPEN_POINTS",
        "MANUFACTURER_REVIEW_READY",
        "OUT_OF_SCOPE",
    }
    one_pager = result["rfq_one_pager"]
    assert one_pager.startswith("# Technical RWDR RFQ Brief")
    assert "Freigabe erfolgt durch Hersteller" in one_pager
    assert "rfq_snapshot" in result and result["rfq_snapshot"]["snapshot_id"]
