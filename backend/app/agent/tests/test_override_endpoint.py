from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

from app.agent.api.models import OverrideItem, OverrideRequest
from app.agent.api.router import session_override_endpoint
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


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        username="tester",
        sub="user-1",
        roles=[],
        scopes=[],
        tenant_id="tenant-1",
    )


@pytest.mark.asyncio
async def test_session_override_endpoint_persists_structured_override(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = _FakeRedisClient()
    monkeypatch.setenv("REDIS_URL", "redis://fake")
    import redis.asyncio as redis_asyncio

    monkeypatch.setattr(redis_asyncio, "Redis", _FakeRedisFactory(fake_redis))

    response = await session_override_endpoint(
        "case-123",
        OverrideRequest(
            overrides=[
                OverrideItem(field_name="medium", value="Wasser"),
                OverrideItem(field_name="pressure_bar", value=6.0, unit="bar"),
                OverrideItem(field_name="temperature_c", value=80.0, unit="°C"),
            ],
            turn_index=2,
        ),
        current_user=_user(),
    )

    assert response.session_id == "case-123"
    assert response.applied_fields == ["medium", "pressure_bar", "temperature_c"]
    assert response.governance.gov_class == "A"
    assert response.governance.inquiry_admissible is True
    assert response.governance.rfq_admissible is True

    persisted = await load_governed_state_async(
        tenant_id="tenant-1",
        session_id="case-123",
        redis_client=fake_redis,
    )
    assert persisted is not None
    assert persisted.observed.user_overrides[-1].field_name == "temperature_c"
    assert persisted.asserted.assertions["medium"].asserted_value == "Wasser"
    assert persisted.asserted.assertions["pressure_bar"].asserted_value == 6.0


@pytest.mark.asyncio
async def test_session_override_endpoint_returns_503_without_redis_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        await session_override_endpoint(
            "case-123",
            OverrideRequest(overrides=[OverrideItem(field_name="medium", value="Wasser")]),
            current_user=_user(),
        )

    assert exc_info.value.status_code == 503
