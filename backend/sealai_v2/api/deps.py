"""M6c — FastAPI dependencies for /api/v2. The validator + pipeline are injected here so tests
override them (``app.dependency_overrides``) with a ``FakeAuthValidator`` + a fake-client pipeline.

P0: ``current_identity`` derives the ``VerifiedIdentity`` ONLY from the verified Bearer token — it
NEVER reads a tenant/session header or param. Auth not configured → 503 (fail-closed, no serving).
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Header, HTTPException

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import AuthError, AuthValidator, Flags, VerifiedIdentity
from sealai_v2.llm.factory import build_client_factory
from sealai_v2.pipeline.pipeline import Pipeline, build_pipeline
from sealai_v2.security.auth import KeycloakJwtValidator


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
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        return validator.validate(authorization[len("Bearer ") :])
    except AuthError:
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
