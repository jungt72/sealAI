"""Tenant scoping (P0) — the non-negotiable seam (build-spec §3/§12, Prinzipien §6).

Threaded through the pipeline and generation path from day one. At M1 there is no
tenant-scoped retrieval yet, but the tenant is a MANDATORY parameter and
``require_tenant`` fails closed on a missing/empty scope — so ``security`` can never
silently become a tenant bypass.
"""

from __future__ import annotations

from dataclasses import dataclass


class TenantScopeError(RuntimeError):
    """Raised when a pipeline/generation call is made without a valid tenant scope (P0)."""


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str


def require_tenant(tenant: TenantContext | None) -> TenantContext:
    """Fail-closed tenant guard. Returns the validated scope or raises ``TenantScopeError``."""
    if (
        tenant is None
        or not isinstance(tenant, TenantContext)
        or not isinstance(tenant.tenant_id, str)
        or not tenant.tenant_id.strip()
    ):
        raise TenantScopeError(
            "tenant scope is mandatory (P0) — no pipeline/generation without a non-empty tenant_id"
        )
    return tenant
