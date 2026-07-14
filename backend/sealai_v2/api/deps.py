"""M6c — FastAPI dependencies for /api/v2. The validator + pipeline are injected here so tests
override them (``app.dependency_overrides``) with a ``FakeAuthValidator`` + a fake-client pipeline.

P0: ``current_identity`` derives the ``VerifiedIdentity`` ONLY from the verified Bearer token — it
NEVER reads a tenant/session header or param. Auth not configured → 503 (fail-closed, no serving).
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

from fastapi import Depends, Header, HTTPException
from starlette.concurrency import run_in_threadpool

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import AuthError, AuthValidator, Flags, VerifiedIdentity
from sealai_v2.llm.factory import build_client_factory
from sealai_v2.pipeline.pipeline import Pipeline, build_pipeline
from sealai_v2.security.auth import KeycloakJwtValidator
from sealai_v2.security.control_metrics import record_auth_denial, record_quota_denial
from sealai_v2.security.cost_control import CostControlPolicy, PostgresCostControlStore

_COST_LOG = logging.getLogger("sealai_v2.provider_admission")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def flags_from_settings(settings: Settings) -> Flags:
    """The production Flags baseline (compliance hint + safety-critical posture) from settings —
    SHARED by every product route (chat, briefing, anfrage) so they run with an IDENTICAL safety
    posture. A route that omits flags silently falls back to ``Flags()`` (both OFF), diverging from
    /chat — that was a real safety bug. Eval columns stay harness-constructed."""
    return Flags(
        compliance_hint=settings.default_compliance_hint,
        safety_critical=settings.default_safety_critical,
    )


@lru_cache(maxsize=1)
def get_validator() -> AuthValidator:
    s = get_settings()
    if not s.auth_jwks_url or not s.auth_issuer or not s.auth_audience:
        raise HTTPException(status_code=503, detail="auth not configured")
    return KeycloakJwtValidator(
        jwks_url=s.auth_jwks_url,
        issuer=s.auth_issuer,
        audience=s.auth_audience,
        tenant_claim=s.auth_tenant_claim,
        jwks_ttl_s=s.auth_jwks_ttl_s,
        jwks_max_ttl_s=s.auth_jwks_max_ttl_s,
        unknown_kid_refresh_interval_s=s.auth_jwks_unknown_kid_refresh_interval_s,
        negative_kid_ttl_s=s.auth_jwks_negative_kid_ttl_s,
        max_negative_kids=s.auth_jwks_max_negative_kids,
        max_token_age_s=s.auth_max_token_age_s,
        clock_skew_s=s.auth_clock_skew_s,
    )


@lru_cache(maxsize=1)
def get_pipeline() -> Pipeline:
    s = get_settings()
    # Per-role provider factory: an all-openai default caches ONE client across roles (byte-
    # identical to the old single-client path); a mixed cell routes each role to its provider.
    return build_pipeline(s, client_for=build_client_factory(s))


def current_identity(
    authorization: str | None = Header(default=None),
    validator: AuthValidator = Depends(get_validator),
) -> VerifiedIdentity:
    """P0: identity from the VERIFIED token only — never a client header/param."""
    if not authorization or not authorization.startswith("Bearer "):
        record_auth_denial("missing_bearer")
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        return validator.validate(authorization[len("Bearer ") :])
    except AuthError:
        record_auth_denial("invalid_token")
        raise HTTPException(status_code=401, detail="invalid token") from None


@lru_cache(maxsize=1)
def get_lead_store():
    """Lead store for /api/v2/anfrage — Postgres (durable, partner/owner-retrievable) when
    ``database_url`` is set, else in-process (eval/CI). Fail-safe to in-process; never crashes."""
    from sealai_v2.db.leads import build_lead_store

    return build_lead_store(get_settings())


@lru_cache(maxsize=1)
def get_partner_registry():
    """Hersteller-Partner registry for the admin CRUD — Postgres (dashboard-editable, durable) when
    ``database_url`` is set, else in-process (eval/CI). Mirrors the pipeline's pool construction so
    both surfaces back the SAME data in prod. Fail-safe to in-process; never crashes startup."""
    s = get_settings()
    if s.database_url:
        try:
            from sealai_v2.db.engine import make_engine, make_sessionmaker
            from sealai_v2.db.hersteller_partner import PostgresPartnerRegistry

            return PostgresPartnerRegistry(
                make_sessionmaker(make_engine(s.database_url))
            )
        except Exception:  # noqa: BLE001 — fail safe to in-process; never crash on startup
            pass
    from sealai_v2.knowledge.hersteller_partner import InProcessPartnerRegistry

    return InProcessPartnerRegistry()


@lru_cache(maxsize=1)
def get_capability_store():
    """Technical manufacturer capabilities, separate from commercial partners."""
    s = get_settings()
    if s.database_url:
        from sealai_v2.db.engine import make_engine, make_sessionmaker
        from sealai_v2.db.manufacturer_capability import (
            PostgresManufacturerCapabilityStore,
        )

        return PostgresManufacturerCapabilityStore(
            make_sessionmaker(make_engine(s.database_url))
        )
    from sealai_v2.knowledge.manufacturer_capability import (
        InProcessManufacturerCapabilityStore,
    )

    return InProcessManufacturerCapabilityStore()


@lru_cache(maxsize=1)
def get_case_decision_store():
    """Durable decision system-of-record with a hermetic in-process test fallback."""
    s = get_settings()
    if s.database_url:
        from sealai_v2.db.case_decisions import PostgresCaseDecisionStore
        from sealai_v2.db.engine import make_engine, make_sessionmaker

        return PostgresCaseDecisionStore(make_sessionmaker(make_engine(s.database_url)))
    from sealai_v2.core.decision_records import InProcessCaseDecisionStore

    return InProcessCaseDecisionStore()


@lru_cache(maxsize=1)
def get_interview_shadow_store():
    """Tenant-scoped shadow telemetry store for the admin-only aggregate report."""
    settings = get_settings()
    if not settings.adaptive_interview_shadow_reporting_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "product_mode_unavailable",
                "mode": "adaptive_interview_shadow_reporting",
                "maturity": "implemented_default_off",
            },
        )
    if settings.database_url:
        from sealai_v2.db.engine import make_engine, make_sessionmaker
        from sealai_v2.db.interview import PostgresInterviewRepository

        return PostgresInterviewRepository(
            make_sessionmaker(make_engine(settings.database_url))
        )
    pipeline = get_pipeline()
    service = pipeline.adaptive_interview_service
    if service is not None:
        return service.repository
    raise HTTPException(
        status_code=503,
        detail="adaptive interview shadow telemetry is unavailable",
    )


@lru_cache(maxsize=1)
def get_knowledge_ledger():
    """Authoritative Postgres review queue; never falls back to process memory."""
    from sealai_v2.knowledge.ledger import build_knowledge_ledger

    settings = get_settings()
    if not settings.database_url:
        raise HTTPException(
            status_code=503, detail="authoritative knowledge ledger is unavailable"
        )
    return build_knowledge_ledger(settings)


def require_admin(
    identity: VerifiedIdentity = Depends(current_identity),
) -> VerifiedIdentity:
    """Owner/admin gate for the Hersteller-Partner management surface (P0 fail-closed). The verified
    token MUST carry the configured admin realm-role (``auth_admin_role``), else 403. Identity (incl.
    roles) comes ONLY from the verified token — never a header/param. This is an ADDITIVE role check;
    the tenant boundary is untouched."""
    if get_settings().auth_admin_role not in identity.roles:
        raise HTTPException(status_code=403, detail="admin role required")
    return identity


def require_manufacturer(
    identity: VerifiedIdentity = Depends(current_identity),
) -> VerifiedIdentity:
    """Manufacturer SELF-SERVICE gate (P0 fail-closed). The verified token MUST carry the configured
    manufacturer realm-role AND a non-empty hersteller_id claim (the partner record it is bound to),
    else 403. Everything downstream is scoped to ``identity.hersteller_id`` — a manufacturer can only
    ever see/edit their OWN record + leads. Additive role check; the tenant boundary is untouched."""
    s = get_settings()
    if s.auth_manufacturer_role not in identity.roles or not identity.hersteller_id:
        raise HTTPException(status_code=403, detail="manufacturer role required")
    return identity


def require_capability_reviewer(
    identity: VerifiedIdentity = Depends(current_identity),
    settings: Settings = Depends(get_settings),
) -> VerifiedIdentity:
    """Independent technical-review role; admin/manufacturer alone is insufficient."""
    if settings.auth_capability_reviewer_role not in identity.roles:
        raise HTTPException(status_code=403, detail="capability reviewer role required")
    return identity


def require_knowledge_reviewer(
    identity: VerifiedIdentity = Depends(current_identity),
    settings: Settings = Depends(get_settings),
) -> VerifiedIdentity:
    """Independent human domain/evidence reviewer for authoritative claims."""
    if settings.auth_knowledge_reviewer_role not in identity.roles:
        raise HTTPException(status_code=403, detail="knowledge reviewer role required")
    return identity


@lru_cache(maxsize=1)
def get_contribution_store():
    """Wissens-Beitrag store — Postgres (durable review queue) when database_url set, else in-process."""
    from sealai_v2.db.contributions import build_contribution_store

    return build_contribution_store(get_settings())


@lru_cache(maxsize=1)
def get_legal_acceptance_store():
    """Legal-Gate acceptance store (Legal-by-Design Phase B) — Postgres (durable, survives a
    restart) when database_url set, else in-process. Mirrors get_contribution_store's pattern."""
    from sealai_v2.db.legal_acceptance import build_legal_acceptance_store

    return build_legal_acceptance_store(get_settings())


def require_legal_acceptance(
    identity: VerifiedIdentity = Depends(current_identity),
    store=Depends(get_legal_acceptance_store),
    settings: Settings = Depends(get_settings),
) -> VerifiedIdentity:
    """Legal-Gate fail-closed guard (Legal-by-Design Phase B, Goal 3). OFF by default via
    ``settings.legal_gate_enabled`` (the draft legal texts this gate protects need an attorney
    review pass before they can lawfully block paying customers; see ``docs/legal-onboarding.md``)
    — while off this dependency is a no-op passthrough, byte-identical to a route with no gate at
    all. Once enabled: 403 unless a CURRENT (version-matching) acceptance row exists for this
    tenant — a stale acceptance (pre-dating a reviewed text bump) does not count, same doctrine as
    the /acceptance endpoint's own version check. ``settings`` is a Depends param (not a direct
    ``get_settings()`` call like require_admin/require_manufacturer use) so tests can flip
    ``legal_gate_enabled`` per-test via ``app.dependency_overrides`` instead of fighting the
    module-level ``lru_cache``."""
    if not settings.legal_gate_enabled:
        return identity
    from sealai_v2.core.legal_doctrine import doctrine_payload

    a = store.get(identity.tenant_id)
    current = doctrine_payload()
    up_to_date = a is not None and (
        a.accepted_terms_version == current["terms_version"]
        and a.accepted_privacy_version == current["privacy_version"]
        and a.accepted_dpa_version == current["dpa_version"]
    )
    if not up_to_date:
        raise HTTPException(
            status_code=403,
            detail="legal_acceptance_required",
        )
    return identity


@lru_cache(maxsize=1)
def get_cost_control_store():
    """Shared production authority. Absence/migration failure denies provider-backed requests."""
    settings = get_settings()
    if not settings.database_url:
        return None
    try:
        from sealai_v2.db.engine import make_engine, make_sessionmaker

        return PostgresCostControlStore(
            make_sessionmaker(make_engine(settings.database_url))
        )
    except Exception:
        raise HTTPException(
            status_code=503, detail="provider cost control unavailable"
        ) from None


async def require_provider_admission(
    identity: VerifiedIdentity = Depends(require_legal_acceptance),
    settings: Settings = Depends(get_settings),
    store=Depends(get_cost_control_store),
):
    """Verified-email + rate/quota/concurrency/budget gate with a crash-safe lease."""
    if not settings.provider_requests_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "provider_kill_switch",
                "message": "provider requests disabled",
            },
        )
    if not identity.email_verified:
        record_auth_denial("email_unverified")
        raise HTTPException(status_code=403, detail="verified email required")
    if store is None:
        raise HTTPException(status_code=503, detail="provider cost control unavailable")
    try:
        decision = await run_in_threadpool(
            store.admit, identity, CostControlPolicy.from_settings(settings)
        )
    except Exception:
        raise HTTPException(
            status_code=503, detail="provider cost control unavailable"
        ) from None
    if not decision.allowed:
        record_quota_denial(decision.reason)
        headers = (
            {"Retry-After": str(decision.retry_after_s)}
            if decision.retry_after_s is not None
            else None
        )
        raise HTTPException(
            status_code=decision.status_code,
            detail={"code": decision.reason, "message": "provider request denied"},
            headers=headers,
        )

    assert decision.admission is not None
    outcome = "error"
    try:
        yield identity
        outcome = "success"
    except asyncio.CancelledError:
        outcome = "cancelled"
        raise
    finally:
        try:
            await run_in_threadpool(
                store.release, decision.admission.request_id, outcome=outcome
            )
        except (
            Exception
        ) as exc:  # lease expiry is the crash-safe fallback; never leak DB detail
            _COST_LOG.error(
                "provider_admission event=release_failed request_id=%s error_type=%s",
                decision.admission.request_id,
                type(exc).__name__,
            )


def require_decision_reviewer(
    identity: VerifiedIdentity = Depends(require_legal_acceptance),
    settings: Settings = Depends(get_settings),
) -> VerifiedIdentity:
    """Human technical-review role; never a manufacturer/component release role."""
    if settings.auth_decision_reviewer_role not in identity.roles:
        raise HTTPException(status_code=403, detail="decision reviewer role required")
    return identity
