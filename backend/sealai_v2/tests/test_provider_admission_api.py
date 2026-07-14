from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from sealai_v2.api import deps
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.security.cost_control import InMemoryCostControlStore


def _enabled(**overrides) -> Settings:
    values = {
        "provider_requests_enabled": True,
        "database_url": "postgresql://quota-authority",
        "provider_budget_contract_sha256": "sha256:" + "a" * 64,
        "provider_subject_requests_per_minute": 10,
        "provider_tenant_requests_per_minute": 20,
        "provider_subject_requests_per_day": 100,
        "provider_tenant_requests_per_day": 200,
        "provider_tenant_requests_per_month": 1000,
        "provider_subject_max_concurrent": 2,
        "provider_tenant_max_concurrent": 10,
        "provider_request_reservation_micros": 100,
        "provider_daily_budget_micros": 1000,
        "provider_monthly_budget_micros": 10_000,
    }
    values.update(overrides)
    # Hermetic dependency test: production Settings deliberately refuses this activation until the
    # external worst-case provider-price contract is approved. model_copy lets us exercise the
    # already-implemented admission boundary without weakening that runtime fail-closed validator.
    return Settings().model_copy(update=values)


def _client(*, identity: VerifiedIdentity, settings: Settings, store) -> TestClient:
    app = FastAPI()

    @app.get("/paid")
    async def paid(
        _: VerifiedIdentity = Depends(deps.require_provider_admission),
    ) -> dict[str, bool]:
        return {"ok": True}

    app.dependency_overrides[deps.require_legal_acceptance] = lambda: identity
    app.dependency_overrides[deps.get_settings] = lambda: settings
    app.dependency_overrides[deps.get_cost_control_store] = lambda: store
    return TestClient(app)


def _identity(*, verified: bool = True) -> VerifiedIdentity:
    return VerifiedIdentity(
        tenant_id="tenant-a",
        session_id="session-a",
        subject="subject-a",
        email_verified=verified,
    )


def test_default_kill_switch_denies_without_touching_provider_store():
    response = _client(identity=_identity(), settings=Settings(), store=None).get(
        "/paid"
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_kill_switch"


def test_unverified_email_and_missing_shared_authority_fail_closed():
    store = InMemoryCostControlStore()
    unverified = _client(
        identity=_identity(verified=False), settings=_enabled(), store=store
    )
    assert unverified.get("/paid").status_code == 403
    unavailable = _client(identity=_identity(), settings=_enabled(), store=None)
    assert unavailable.get("/paid").status_code == 503


def test_subject_rate_limit_is_atomic_and_returns_retry_after():
    store = InMemoryCostControlStore()
    settings = _enabled(
        provider_subject_requests_per_minute=1,
        provider_tenant_requests_per_minute=2,
    )
    client = _client(identity=_identity(), settings=settings, store=store)
    assert client.get("/paid").status_code == 200
    denied = client.get("/paid")
    assert denied.status_code == 429
    assert denied.json()["detail"]["code"] == "subject_rate"
    assert int(denied.headers["Retry-After"]) >= 1


def test_daily_budget_reservation_is_not_refunded_after_success():
    store = InMemoryCostControlStore()
    settings = _enabled(
        provider_request_reservation_micros=100,
        provider_daily_budget_micros=100,
    )
    client = _client(identity=_identity(), settings=settings, store=store)
    assert client.get("/paid").status_code == 200
    denied = client.get("/paid")
    assert denied.status_code == 402
    assert denied.json()["detail"]["code"] == "provider_daily_budget"


def test_request_scoped_admission_lease_covers_stream_body_generation():
    store = InMemoryCostControlStore()
    app = FastAPI()

    @app.get("/stream")
    async def stream(
        _: VerifiedIdentity = Depends(deps.require_provider_admission, scope="request"),
    ) -> StreamingResponse:
        async def body():
            yield str(store.summary()["active_requests"])

        return StreamingResponse(body(), media_type="text/plain")

    app.dependency_overrides[deps.require_legal_acceptance] = lambda: _identity()
    app.dependency_overrides[deps.get_settings] = lambda: _enabled()
    app.dependency_overrides[deps.get_cost_control_store] = lambda: store
    response = TestClient(app).get("/stream")
    assert response.status_code == 200
    assert response.text == "1"
    assert store.summary()["active_requests"] == 0
