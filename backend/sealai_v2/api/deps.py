"""M6c — FastAPI dependencies for /api/v2. The validator + pipeline are injected here so tests
override them (``app.dependency_overrides``) with a ``FakeAuthValidator`` + a fake-client pipeline.

P0: ``current_identity`` derives the ``VerifiedIdentity`` ONLY from the verified Bearer token — it
NEVER reads a tenant/session header or param. Auth not configured → 503 (fail-closed, no serving).
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Header, HTTPException

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import AuthError, AuthValidator, VerifiedIdentity
from sealai_v2.llm.factory import build_client_factory
from sealai_v2.pipeline.pipeline import Pipeline, build_pipeline
from sealai_v2.security.auth import KeycloakJwtValidator


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


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
