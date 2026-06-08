from __future__ import annotations

import pytest

from sealai_v2.security.tenant import TenantContext, TenantScopeError, require_tenant


def test_valid_tenant_passes():
    assert require_tenant(TenantContext("acme")).tenant_id == "acme"


def test_missing_or_empty_tenant_fails_closed():
    for bad in (None, TenantContext(""), TenantContext("   ")):
        with pytest.raises(TenantScopeError):
            require_tenant(bad)  # type: ignore[arg-type]
